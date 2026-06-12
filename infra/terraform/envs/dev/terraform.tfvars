# Dev environment variable overrides
# Replace with your organization's actual subscription ID before applying.

subscription_id = "00000000-0000-0000-0000-000000000000"
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
