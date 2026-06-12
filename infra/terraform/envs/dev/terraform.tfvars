# Dev environment variable overrides
# Replace with your organization's actual subscription ID before applying.

subscription_id = "990c37af-3c42-4bd0-a376-600bc37d71ff"
location        = "eastus2"
environment     = "dev"

compute_min_nodes = 0
compute_max_nodes = 2
compute_vm_size   = "Standard_DS3_v2"

tags = {
  project     = "healthcare-ai-assistant"
  environment = "dev"
  owner       = "ml-platform-team"
  costcenter  = "hcai-dev"
}
