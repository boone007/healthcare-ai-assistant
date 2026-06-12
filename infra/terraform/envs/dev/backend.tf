# Remote state backend (Azure Storage)
#
# Replace placeholder values with your organization's Terraform state
# storage account, or configure via `terraform init -backend-config=...`.

terraform {
  backend "azurerm" {
    resource_group_name  = "rg-hcai-tfstate"
    storage_account_name = "sthcaitfstate001"
    container_name        = "tfstate"
    key                   = "hcai-dev.tfstate"
  }
}
