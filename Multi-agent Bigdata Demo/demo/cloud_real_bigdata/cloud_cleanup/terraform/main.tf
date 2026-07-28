locals {
  cleanup_policy_ids = toset([
    "MRSFullAccessPolicy",
    "ECSFullPolicy",
    "VPCFullAccessPolicy",
    "EIPFullAccessPolicy",
    "OBSAFullAccessPolicy",
    "DataArtsStudioFullAccessPolicy"
  ])
}

resource "huaweicloud_identity_policy_agency_attach" "cleanup" {
  for_each  = local.cleanup_policy_ids
  agency_id = var.execution_agency_id
  policy_id = each.value
}

resource "huaweicloud_fgs_function" "cleanup" {
  name                  = var.function_name
  app                   = "default"
  description           = "Cloud-side cleanup controller for the SAT Agentic demo."
  handler               = "index.handler"
  memory_size           = 256
  timeout               = 600
  runtime               = "Python3.10"
  code_type             = "zip"
  code_filename         = basename(var.package_path)
  func_code             = filebase64(var.package_path)
  functiongraph_version = "v2"
  agency                = var.configuration_agency_name
  app_agency            = var.execution_agency_name
  enable_lts_log        = false
  user_data = jsonencode({
    cleanup_config = var.cleanup_config_json
  })

  tags = {
    purpose    = "sat-agentic-demo-cleanup"
    expires_at = "2026-07-27"
  }

  depends_on = [huaweicloud_identity_policy_agency_attach.cleanup]
}

resource "huaweicloud_fgs_trigger" "cleanup" {
  function_urn = huaweicloud_fgs_function.cleanup.urn
  type         = "TIMER"
  status       = var.trigger_status

  timer {
    name          = var.trigger_name
    schedule_type = "Cron"
    schedule      = var.cleanup_schedule
  }
}
