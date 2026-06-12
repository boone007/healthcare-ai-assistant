variable "name" {
  description = "Name of the Application Insights instance, e.g. appi-hcai-dev"
  type        = string
}

variable "resource_group_name" {
  description = "Name of the resource group to deploy resources into"
  type        = string
}

variable "location" {
  description = "Azure region for resources"
  type        = string
}

variable "log_retention_days" {
  description = "Log Analytics workspace data retention in days"
  type        = number
  default     = 30
}

variable "tags" {
  description = "Common resource tags"
  type        = map(string)
  default     = {}
}
