#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shlex
import time
from pathlib import Path

import paramiko


JAVA_SOURCE = r'''
package com.dockone.flink;

import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;

import org.apache.flink.api.java.utils.ParameterTool;
import org.apache.flink.streaming.api.datastream.DataStream;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.apache.flink.streaming.api.functions.sink.RichSinkFunction;
import org.apache.flink.streaming.api.functions.source.SourceFunction;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.PartitionInfo;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.serialization.StringDeserializer;
import com.obs.services.ObsClient;

public class KafkaToObsRaw {
    public static void main(String[] args) throws Exception {
        ParameterTool params = ParameterTool.fromArgs(args);
        String bootstrap = params.getRequired("bootstrap");
        String topic = params.getRequired("topic");
        String group = params.get("group", "mrs-flink-contracts-to-obs");
        String output = params.getRequired("output");
        long maxMessages = params.getLong("maxMessages", 0L);
        int pollMillis = params.getInt("pollMillis", 1000);
        String obsAk = params.get("obsAk", System.getenv("DOCKONE_OBS_AK"));
        String obsSk = params.get("obsSk", System.getenv("DOCKONE_OBS_SK"));
        String obsEndpoint = params.get("obsEndpoint", System.getenv("DOCKONE_OBS_ENDPOINT"));
        ObsTarget target = ObsTarget.fromObsUrl(output);

        StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();
        env.setParallelism(1);
        env.getConfig().setGlobalJobParameters(params);

        DataStream<String> records = env
            .addSource(new BoundedKafkaJsonSource(bootstrap, topic, group, maxMessages, pollMillis))
            .name("DMS Kafka billing.contracts bounded source")
            .setParallelism(1);

        records
            .addSink(new ObsSdkJsonSink(target.bucket, target.objectKeyPrefix, obsAk, obsSk, obsEndpoint))
            .name("OBS SDK raw JSON sink")
            .setParallelism(1);

        env.execute("dockone-dms-kafka-to-obs-raw-json");
    }

    public static final class ObsTarget {
        public final String bucket;
        public final String objectKeyPrefix;

        private ObsTarget(String bucket, String objectKeyPrefix) {
            this.bucket = bucket;
            this.objectKeyPrefix = objectKeyPrefix;
        }

        public static ObsTarget fromObsUrl(String output) {
            if (!output.startsWith("obs://")) {
                throw new IllegalArgumentException("OBS output must start with obs:// : " + output);
            }
            String path = output.substring("obs://".length());
            int slash = path.indexOf('/');
            if (slash <= 0 || slash >= path.length() - 1) {
                throw new IllegalArgumentException("OBS output must include bucket and key prefix: " + output);
            }
            String bucket = path.substring(0, slash);
            String key = path.substring(slash + 1);
            while (key.startsWith("/")) {
                key = key.substring(1);
            }
            while (key.endsWith("/")) {
                key = key.substring(0, key.length() - 1);
            }
            return new ObsTarget(bucket, key);
        }
    }

    public static final class ObsSdkJsonSink extends RichSinkFunction<String> {
        private final String bucket;
        private final String objectKeyPrefix;
        private final String obsAk;
        private final String obsSk;
        private final String obsEndpoint;
        private final List<String> rows = new ArrayList<>();

        public ObsSdkJsonSink(String bucket, String objectKeyPrefix, String obsAk, String obsSk, String obsEndpoint) {
            this.bucket = bucket;
            this.objectKeyPrefix = objectKeyPrefix;
            this.obsAk = obsAk;
            this.obsSk = obsSk;
            this.obsEndpoint = obsEndpoint;
        }

        @Override
        public void invoke(String value, Context context) {
            rows.add(value);
        }

        @Override
        public void close() {
            if (rows.isEmpty()) {
                System.out.println("DockOne OBS SDK sink closed with zero rows.");
                return;
            }
            String ak = (obsAk == null || obsAk.isEmpty()) ? System.getenv("DOCKONE_OBS_AK") : obsAk;
            String sk = (obsSk == null || obsSk.isEmpty()) ? System.getenv("DOCKONE_OBS_SK") : obsSk;
            String endpoint = (obsEndpoint == null || obsEndpoint.isEmpty()) ? System.getenv("DOCKONE_OBS_ENDPOINT") : obsEndpoint;
            if (ak == null || ak.isEmpty() || sk == null || sk.isEmpty()) {
                throw new IllegalStateException("Missing DOCKONE_OBS_AK/DOCKONE_OBS_SK in Flink container environment.");
            }
            if (endpoint == null || endpoint.isEmpty()) {
                endpoint = "obs.la-south-2.myhuaweicloud.com";
            }
            StringBuilder body = new StringBuilder();
            for (String row : rows) {
                body.append(row).append('\n');
            }
            byte[] payload = body.toString().getBytes(StandardCharsets.UTF_8);
            String key = objectKeyPrefix.endsWith(".json")
                ? objectKeyPrefix
                : objectKeyPrefix + "/part-flink-" + System.currentTimeMillis() + ".json";
            ObsClient client = new ObsClient(ak, sk, endpoint);
            try {
                client.putObject(bucket, key, new ByteArrayInputStream(payload));
                System.out.println("DockOne OBS SDK sink wrote " + rows.size() + " rows, bytes=" + payload.length + ", key=" + key);
            } finally {
                try {
                    client.close();
                } catch (Exception ignored) {
                }
            }
        }
    }

    public static final class BoundedKafkaJsonSource implements SourceFunction<String> {
        private final String bootstrap;
        private final String topic;
        private final String group;
        private final long maxMessages;
        private final int pollMillis;
        private volatile boolean running = true;

        public BoundedKafkaJsonSource(String bootstrap, String topic, String group, long maxMessages, int pollMillis) {
            this.bootstrap = bootstrap;
            this.topic = topic;
            this.group = group;
            this.maxMessages = maxMessages;
            this.pollMillis = pollMillis;
        }

        @Override
        public void run(SourceContext<String> ctx) throws Exception {
            Properties props = new Properties();
            props.setProperty(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrap);
            props.setProperty(ConsumerConfig.GROUP_ID_CONFIG, group);
            props.setProperty(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class.getName());
            props.setProperty(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class.getName());
            props.setProperty(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
            props.setProperty(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, "false");
            props.setProperty(ConsumerConfig.CLIENT_ID_CONFIG, "dockone-mrs-flink-" + System.currentTimeMillis());

            long emitted = 0L;
            try (KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props)) {
                List<PartitionInfo> partitionInfos = consumer.partitionsFor(topic);
                if (partitionInfos == null || partitionInfos.isEmpty()) {
                    throw new IllegalStateException("Kafka topic has no partitions or is not visible: " + topic);
                }

                List<TopicPartition> partitions = new ArrayList<>();
                for (PartitionInfo info : partitionInfos) {
                    partitions.add(new TopicPartition(topic, info.partition()));
                }

                consumer.assign(partitions);
                consumer.seekToBeginning(partitions);
                Map<TopicPartition, Long> endOffsets = consumer.endOffsets(partitions);
                Map<TopicPartition, Long> consumedOffsets = new HashMap<>();

                while (running) {
                    boolean allDone = true;
                    for (TopicPartition partition : partitions) {
                        long end = endOffsets.get(partition);
                        long position = consumer.position(partition);
                        consumedOffsets.put(partition, position);
                        if (position < end) {
                            allDone = false;
                        }
                    }
                    if (allDone) {
                        break;
                    }
                    if (maxMessages > 0 && emitted >= maxMessages) {
                        break;
                    }

                    ConsumerRecords<String, String> records = consumer.poll(Duration.ofMillis(pollMillis));
                    synchronized (ctx.getCheckpointLock()) {
                        for (ConsumerRecord<String, String> record : records) {
                            Long end = endOffsets.get(new TopicPartition(record.topic(), record.partition()));
                            if (end != null && record.offset() < end) {
                                ctx.collect(record.value());
                                emitted++;
                                if (maxMessages > 0 && emitted >= maxMessages) {
                                    break;
                                }
                            }
                        }
                    }
                }

                System.out.println("DockOne bounded Kafka source completed. topic=" + topic
                    + ", emitted=" + emitted
                    + ", endOffsets=" + endOffsets
                    + ", finalPositions=" + consumedOffsets);
            }
        }

        @Override
        public void cancel() {
            running = false;
        }
    }
}
'''


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compile and run a bounded Kafka->OBS JSON Flink jar on MRS Flink via the runner ECS.")
    parser.add_argument("--runner-ip", default=os.environ.get("RUNNER_ECS_PUBLIC_IP", "119.8.147.99"))
    parser.add_argument("--master-ip", default=os.environ.get("MRS_FLINK_MASTER_IP", "192.168.12.66"))
    parser.add_argument("--bootstrap", default=os.environ.get("DMS_KAFKA_BOOTSTRAP_SERVERS", "192.168.11.202:9093"))
    parser.add_argument("--topic", default=os.environ.get("DMS_KAFKA_TOPIC", "dockone.billing.contracts"))
    parser.add_argument("--group-id", default=None)
    parser.add_argument("--bucket", default=os.environ.get("DEPLOYMENT_OBS_BUCKET", "hwstaff-retail-lakehouse-09d63c-20260622"))
    parser.add_argument("--output-prefix", default=None)
    parser.add_argument("--max-messages", type=int, default=0)
    parser.add_argument(
        "--explicit-obs-credentials",
        action="store_true",
        help="Inject OBS AK/SK as transient Flink -D properties. Output is redacted; no secrets are written locally.",
    )
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--summary", default=str(Path("runs") / "mrs-flink-kafka-to-obs-jar-run.json"))
    return parser.parse_args()


def quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value)[:64]


def ssh_exec(host: str, user: str, password: str, command: str, timeout: int) -> tuple[int, str, str]:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        host,
        username=user,
        password=password,
        look_for_keys=False,
        allow_agent=False,
        timeout=30,
        banner_timeout=30,
        auth_timeout=30,
    )
    try:
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        code = stdout.channel.recv_exit_status()
        return code, stdout.read().decode("utf-8", "replace"), stderr.read().decode("utf-8", "replace")
    finally:
        client.close()


def build_remote_script() -> str:
    return r'''
import base64
import json
import os
import shlex
import time

import paramiko

master = os.environ["MRS_MASTER"]
password = os.environ["MRS_PASSWORD"]
java_source = base64.b64decode(os.environ["JAVA_SOURCE_B64"]).decode("utf-8")
bootstrap = os.environ["KAFKA_BOOTSTRAP"]
topic = os.environ["KAFKA_TOPIC"]
group_id = os.environ["KAFKA_GROUP_ID"]
output = os.environ["OBS_OUTPUT"]
max_messages = os.environ["MAX_MESSAGES"]
explicit_obs_credentials = os.environ.get("EXPLICIT_OBS_CREDENTIALS") == "1"
obs_ak = os.environ.get("OBS_AK", "")
obs_sk = os.environ.get("OBS_SK", "")
obs_token = os.environ.get("OBS_TOKEN", "")
obs_endpoint = os.environ.get("OBS_ENDPOINT", "")
remote_timeout = int(os.environ.get("REMOTE_TIMEOUT", "1800"))
run_id = os.environ.get("RUN_ID", str(int(time.time())))
workdir = f"/tmp/dockone_flink_kafka_to_obs_{run_id}"
source_path = f"{workdir}/src/com/dockone/flink/KafkaToObsRaw.java"
jar_path = f"{workdir}/dockone-kafka-to-obs-flink.jar"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(master, username="root", password=password, look_for_keys=False, allow_agent=False, timeout=30, banner_timeout=30, auth_timeout=30)
try:
    mkdir_cmd = f"rm -rf {shlex.quote(workdir)} && mkdir -p {shlex.quote(os.path.dirname(source_path))} {shlex.quote(workdir + '/classes')}"
    stdin, stdout, stderr = c.exec_command(mkdir_cmd, timeout=120)
    mkdir_code = stdout.channel.recv_exit_status()
    if mkdir_code != 0:
        raise RuntimeError(stdout.read().decode("utf-8", "replace") + stderr.read().decode("utf-8", "replace"))

    encoded_source = base64.b64encode(java_source.encode("utf-8")).decode("ascii")
    stdin, stdout, stderr = c.exec_command(f"base64 -d > {shlex.quote(source_path)}", timeout=120)
    stdin.write(encoded_source)
    stdin.channel.shutdown_write()
    write_code = stdout.channel.recv_exit_status()
    if write_code != 0:
        raise RuntimeError(stdout.read().decode("utf-8", "replace") + stderr.read().decode("utf-8", "replace"))

    compile_inner = f"""
set -e
export JAVA_HOME=/opt/Bigdata/client/JDK/jdk1.8.0_422
export PATH=$JAVA_HOME/bin:$PATH
export FLINK_HOME=/opt/Bigdata/client/Flink/flink
$JAVA_HOME/bin/javac -source 1.8 -target 1.8 -encoding UTF-8 -cp "$FLINK_HOME/lib/*:$FLINK_HOME/opt/*:/opt/Bigdata/share/flink/*:/opt/Bigdata/client/HDFS/hadoop/share/hadoop/common/lib/*" -d {shlex.quote(workdir + '/classes')} {shlex.quote(source_path)}
$JAVA_HOME/bin/jar cf {shlex.quote(jar_path)} -C {shlex.quote(workdir + '/classes')} .
chmod -R a+rX {shlex.quote(workdir)}
chmod 0644 {shlex.quote(jar_path)}
ls -lh {shlex.quote(jar_path)}
"""
    stdin, stdout, stderr = c.exec_command("bash -lc " + shlex.quote(compile_inner), timeout=300)
    compile_code = stdout.channel.recv_exit_status()
    compile_stdout = stdout.read().decode("utf-8", "replace")
    compile_stderr = stderr.read().decode("utf-8", "replace")

    if compile_code != 0:
        print(json.dumps({
            "stage": "compile",
            "code": compile_code,
            "stdout": compile_stdout,
            "stderr": compile_stderr,
            "workdir": workdir,
        }, ensure_ascii=False))
        raise SystemExit(compile_code)

    flink_args = [
        "/opt/Bigdata/client/Flink/flink/bin/flink",
        "run",
    ]
    if explicit_obs_credentials:
        flink_args.extend([
            f"-Dcontainerized.master.env.DOCKONE_OBS_AK={obs_ak}",
            f"-Dcontainerized.master.env.DOCKONE_OBS_SK={obs_sk}",
            f"-Dcontainerized.taskmanager.env.DOCKONE_OBS_AK={obs_ak}",
            f"-Dcontainerized.taskmanager.env.DOCKONE_OBS_SK={obs_sk}",
        ])
        if obs_token:
            flink_args.extend([
                f"-Dcontainerized.master.env.DOCKONE_OBS_TOKEN={obs_token}",
                f"-Dcontainerized.taskmanager.env.DOCKONE_OBS_TOKEN={obs_token}",
            ])
        if obs_endpoint:
            flink_args.extend([
                f"-Dcontainerized.master.env.DOCKONE_OBS_ENDPOINT={obs_endpoint}",
                f"-Dcontainerized.taskmanager.env.DOCKONE_OBS_ENDPOINT={obs_endpoint}",
            ])
    flink_args.extend([
        "-m",
        "yarn-cluster",
        "-ynm",
        "dockone-kafka-to-obs",
        "-c",
        "com.dockone.flink.KafkaToObsRaw",
        jar_path,
        "--bootstrap",
        bootstrap,
        "--topic",
        topic,
        "--group",
        group_id,
        "--output",
        output,
        "--maxMessages",
        max_messages,
    ])
    if explicit_obs_credentials:
        flink_args.extend([
            "--obsAk",
            obs_ak,
            "--obsSk",
            obs_sk,
            "--obsEndpoint",
            obs_endpoint or "obs.la-south-2.myhuaweicloud.com",
        ])
    run_inner = (
        "source /opt/Bigdata/client/bigdata_env >/tmp/dockone_flink_env.log 2>&1; "
        "export HADOOP_USER_NAME=omm; "
        "export HADOOP_CONF_DIR=${HADOOP_CONF_DIR:-/opt/Bigdata/client/Flink/flink/conf}; "
        + " ".join(shlex.quote(item) for item in flink_args)
    )
    run_cmd = "su - omm -s /bin/bash -c " + shlex.quote(run_inner)
    started = time.time()
    stdin, stdout, stderr = c.exec_command(run_cmd, timeout=remote_timeout)
    run_code = stdout.channel.recv_exit_status()
    run_stdout = stdout.read().decode("utf-8", "replace")
    run_stderr = stderr.read().decode("utf-8", "replace")
    def redact(text):
        for secret in [obs_ak, obs_sk, obs_token]:
            if secret:
                text = text.replace(secret, "***REDACTED***")
        return text
    print(json.dumps({
        "stage": "run",
        "code": run_code,
        "duration_seconds": round(time.time() - started, 2),
        "workdir": workdir,
        "jar_path": jar_path,
        "output": output,
        "topic": topic,
        "group_id": group_id,
        "compile_stdout": compile_stdout,
        "compile_stderr": compile_stderr,
        "stdout": redact(run_stdout),
        "stderr": redact(run_stderr),
    }, ensure_ascii=False))
    raise SystemExit(run_code)
finally:
    c.close()
'''


def main() -> None:
    args = parse_args()
    run_id = time.strftime("%Y%m%d%H%M%S")
    group_id = args.group_id or f"mrs-flink-contracts-to-obs-{run_id}"
    output_prefix = args.output_prefix or (
        f"raw_flink/dockone_exampleapp/kfk.prd.cdc.dockone_exampleapp.billing.contracts/run={run_id}"
    )
    output = output_prefix if output_prefix.startswith("obs://") else f"obs://{args.bucket}/{output_prefix.strip('/')}"

    runner_password = os.environ["DWS_PASSWORD"]
    mrs_password = os.environ["MRS_PASSWORD"]
    remote_script_b64 = base64.b64encode(build_remote_script().encode("utf-8")).decode("ascii")
    java_source_b64 = base64.b64encode(JAVA_SOURCE.encode("utf-8")).decode("ascii")
    remote_cmd = (
        f"MRS_MASTER={quote(args.master_ip)} "
        f"MRS_PASSWORD={quote(mrs_password)} "
        f"JAVA_SOURCE_B64={quote(java_source_b64)} "
        f"KAFKA_BOOTSTRAP={quote(args.bootstrap)} "
        f"KAFKA_TOPIC={quote(args.topic)} "
        f"KAFKA_GROUP_ID={quote(group_id)} "
        f"OBS_OUTPUT={quote(output)} "
        f"MAX_MESSAGES={args.max_messages} "
        f"EXPLICIT_OBS_CREDENTIALS={'1' if args.explicit_obs_credentials else '0'} "
        f"OBS_AK={quote(os.environ.get('HUAWEICLOUD_ACCESS_KEY', '') if args.explicit_obs_credentials else '')} "
        f"OBS_SK={quote(os.environ.get('HUAWEICLOUD_SECRET_KEY', '') if args.explicit_obs_credentials else '')} "
        f"OBS_TOKEN={quote(os.environ.get('HUAWEICLOUD_SECURITY_TOKEN', '') if args.explicit_obs_credentials else '')} "
        f"OBS_ENDPOINT={quote('obs.' + os.environ.get('HUAWEICLOUD_REGION', 'la-south-2') + '.myhuaweicloud.com' if args.explicit_obs_credentials else '')} "
        f"REMOTE_TIMEOUT={args.timeout_seconds} "
        f"RUN_ID={quote(safe_name(run_id))} "
        f"python3 -c \"import base64; exec(base64.b64decode('{remote_script_b64}').decode('utf-8'))\""
    )

    started = time.perf_counter()
    code, stdout, stderr = ssh_exec(args.runner_ip, "root", runner_password, remote_cmd, timeout=args.timeout_seconds + 180)
    result = {
        "exit_code": code,
        "duration_seconds": round(time.perf_counter() - started, 2),
        "runner_ip": args.runner_ip,
        "master_ip": args.master_ip,
        "bootstrap": args.bootstrap,
        "topic": args.topic,
        "group_id": group_id,
        "output": output,
        "stdout": stdout,
        "stderr": stderr,
    }
    for secret in [
        os.environ.get("HUAWEICLOUD_ACCESS_KEY", ""),
        os.environ.get("HUAWEICLOUD_SECRET_KEY", ""),
        os.environ.get("HUAWEICLOUD_SECURITY_TOKEN", ""),
    ]:
        if secret:
            result["stdout"] = result["stdout"].replace(secret, "***REDACTED***")
            result["stderr"] = result["stderr"].replace(secret, "***REDACTED***")
    Path(args.summary).parent.mkdir(parents=True, exist_ok=True)
    Path(args.summary).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "summary": args.summary,
        "exit_code": code,
        "duration_seconds": result["duration_seconds"],
        "topic": args.topic,
        "group_id": group_id,
        "output": output,
        "stdout_bytes": len(stdout),
        "stderr_bytes": len(stderr),
    }, ensure_ascii=False, indent=2))
    if result["stdout"]:
        print(result["stdout"][-4000:])
    if result["stderr"]:
        print(result["stderr"][-4000:])


if __name__ == "__main__":
    main()
