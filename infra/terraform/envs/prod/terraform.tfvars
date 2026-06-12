# Prod environment variable overrides
# Replace with your organization's actual subscription ID before applying.

subscription_id = "00000000-0000-0000-0000-000000000000"
location        = "eastus2"
environment     = "prod"

compute_min_nodes = 1
compute_max_nodes = 4
compute_vm_size   = "Standard_DS4_v2"

tags = {
  project     = "healthcare-ai-assistant"
  environment = "prod"
  owner       = "ml-platform-team"
  costcenter  = "hcai-prod"
}
