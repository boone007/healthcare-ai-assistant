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

variable "tags" {
  description = "Common resource tags"
  type        = map(string)
  default     = {}
}
