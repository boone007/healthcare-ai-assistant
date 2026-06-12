variable "subscription_id" {
  description = "Azure subscription ID to deploy resources into"
  type        = string
  default     = "00000000-0000-0000-0000-000000000000"
}

variable "location" {
  description = "Azure region for all resources"
  type        = string
  default     = "eastus2"
}

variable "environment" {
  description = "Environment short name, used in resource naming and tags"
  type        = string
  default     = "prod"
}

variable "tags" {
  description = "Common resource tags applied to all resources"
  type        = map(string)
  default = {
    project     = "healthcare-ai-assistant"
    environment = "prod"
    owner       = "ml-platform-team"
    costcenter  = "hcai-prod"
  }
}

variable "compute_min_nodes" {
  description = "Minimum node count for the AML training compute cluster"
  type        = number
  default     = 1
}

variable "compute_max_nodes" {
  description = "Maximum node count for the AML training compute cluster"
  type        = number
  default     = 4
}

variable "compute_vm_size" {
  description = "VM SKU for the AML training compute cluster"
  type        = string
  default     = "Standard_DS4_v2"
}
