#!/usr/bin/env bash
# Run on the ECS. DB_BACKUP_CNF is a mode-600 MySQL client file with the RDS login and CA.
set -euo pipefail
umask 077
exec 9>/run/lock/data-ppl-backup.lock
flock -n 9 || exit 0
cd "$(dirname "$0")/.."
: "${DB_BACKUP_CNF:?Set DB_BACKUP_CNF to a protected MySQL client option file}"
: "${BACKUP_DIR:?Set BACKUP_DIR to a protected backup directory}"
mkdir -p "$BACKUP_DIR"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
target="$BACKUP_DIR/$stamp"
mkdir "$target"
# Take the database snapshot first, then copy immutable files. Files are fsynced
# before metadata commits and never physically deleted. Extra files created
# after the snapshot have no restored metadata and cannot be downloaded.
dump_options=(--single-transaction --no-tablespaces --hex-blob)
dump_help=$(mysqldump --no-defaults --help)
if [[ $dump_help == *set-gtid-purged* ]]; then dump_options+=(--set-gtid-purged=OFF); fi
mysqldump --defaults-extra-file="$DB_BACKUP_CNF" "${dump_options[@]}" -- "${DB_NAME:-data_ppl}" > "$target/database.sql"
backup_paths=(uploads)
if [ -d data/private ]; then backup_paths+=(private); fi
tar -czf "$target/uploads.tar.gz" -C data "${backup_paths[@]}"
(cd "$target" && sha256sum database.sql uploads.tar.gz > SHA256SUMS)
# Retain seven successful local recovery points; cloud retention is configured separately.
python3 - "$BACKUP_DIR" <<'PY'
from pathlib import Path
import re,shutil,sys
root=Path(sys.argv[1]).resolve()
assert root==Path('/var/backups/data-ppl-management')
points=sorted(p for p in root.iterdir() if re.fullmatch(r'\d{8}T\d{6}Z',p.name) and p.is_dir() and not p.is_symlink() and (p/'SHA256SUMS').is_file())
for old in points[:-7]:
    assert old.resolve().parent==root
    shutil.rmtree(old)
PY
echo "Consistent backup saved: $target. Keep the scheduled cloud server backup and RDS automated backups enabled."
