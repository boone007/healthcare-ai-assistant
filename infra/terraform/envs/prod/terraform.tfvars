# Prod environment variable overrides
# Replace with your organization's actual subscription ID before applying.

subscription_id = "990c37af-3c42-4bd0-a376-600bc37d71ff"
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
