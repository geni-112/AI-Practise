# Copy this file outside the package and fill values in your shell/session.
# Do not commit or share the filled version.

# Option A: temporary AK/SK already acquired by your operator or secret manager.
$env:HUAWEICLOUD_ACCESS_KEY = ""
$env:HUAWEICLOUD_SECRET_KEY = ""
$env:HUAWEICLOUD_SECURITY_TOKEN = ""
$env:HUAWEICLOUD_PROJECT_ID = ""

# Option B: IAM password flow. Prefer a secure secret manager over plain shell history.
$env:HUAWEICLOUD_DOMAIN_NAME = ""
$env:HUAWEICLOUD_IAM_USER_NAME = ""
$env:HUAWEICLOUD_IAM_PASSWORD = ""

# Region defaults for the Chile stable path.
$env:HUAWEICLOUD_REGION = "la-south-2"
$env:HUAWEICLOUD_PROJECT_NAME = "la-south-2"
$env:OBS_ENDPOINT = "https://obs.la-south-2.myhuaweicloud.com"
$env:DEMO_BUCKET = "docktest"
