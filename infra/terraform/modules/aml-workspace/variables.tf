variable "name" {
  description = "Name of the Azure ML workspace, e.g. mlw-hcai-dev"
  type        = string
}

variable "resource_group_name" {
  description = "Name of the resource group to deploy the workspace into"
  type        = string
}

variable "location" {
  description = "Azure region for the workspace"
  type        = string
}

variable "storage_account_id" {
  description = "Resource ID of the storage account used as the workspace's default datastore"
  type        = string
}

variable "key_vault_id" {
  description = "Resource ID of the Key Vault associated with the workspace"
  type        = string
}

variable "application_insights_id" {
  description = "Resource ID of the Application Insights instance associated with the workspace"
  type        = string
}

variable "container_registry_name" {
  description = "Globally-unique name for the Azure Container Registry backing the workspace, e.g. acrhcaidev001"
  type        = string
}

variable "container_registry_sku" {
  description = "SKU for the Azure Container Registry"
  type        = string
  default     = "Basic"
}

variable "public_network_access_enabled" {
  description = "Whether the workspace is reachable over the public internet (set false for prod with private endpoints)"
  type        = bool
  default     = true
}

variable "tags" {
  description = "Common resource tags"
  type        = map(string)
  default     = {}
}
