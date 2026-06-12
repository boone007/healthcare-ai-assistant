variable "name" {
  description = "Globally-unique storage account name (lowercase, no hyphens, <=24 chars), e.g. sthcaidev001"
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9]{3,24}$", var.name))
    error_message = "Storage account name must be 3-24 lowercase alphanumeric characters."
  }
}

variable "resource_group_name" {
  description = "Name of the resource group to deploy the storage account into"
  type        = string
}

variable "location" {
  description = "Azure region for the storage account"
  type        = string
}

variable "account_tier" {
  description = "Storage account performance tier"
  type        = string
  default     = "Standard"
}

variable "replication_type" {
  description = "Storage account replication type (LRS, GRS, ZRS, etc.)"
  type        = string
  default     = "LRS"
}

variable "is_hns_enabled" {
  description = <<-EOT
    Whether to enable ADLS Gen2 hierarchical namespace. Required for the data
    lake storage account, but must be false for a storage account used as an
    Azure ML workspace's default storage account (the AML control plane
    rejects HNS-enabled storage with "Cannot use storage with HNS enabled").
  EOT
  type        = bool
  default     = true
}

variable "create_data_lake_containers" {
  description = "Whether to create the raw/curated/models/monitoring data lake containers. Set to false for a storage account dedicated to an AML workspace's default storage."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Common resource tags"
  type        = map(string)
  default     = {}
}
