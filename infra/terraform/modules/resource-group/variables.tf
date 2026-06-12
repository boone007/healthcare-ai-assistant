variable "name" {
  description = "Name of the resource group, e.g. rg-hcai-dev"
  type        = string
}

variable "location" {
  description = "Azure region for the resource group, e.g. eastus2"
  type        = string
}

variable "tags" {
  description = "Common resource tags applied to the resource group"
  type        = map(string)
  default     = {}
}
