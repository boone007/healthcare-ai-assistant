variable "vnet_name" {
  description = "Name of the virtual network, e.g. vnet-hcai-dev"
  type        = string
}

variable "resource_group_name" {
  description = "Name of the resource group to deploy networking resources into"
  type        = string
}

variable "location" {
  description = "Azure region for networking resources"
  type        = string
}

variable "address_space" {
  description = "CIDR address space for the virtual network"
  type        = string
  default     = "10.20.0.0/16"
}

variable "aml_subnet_prefix" {
  description = "CIDR prefix for the AML compute/private-endpoint subnet"
  type        = string
  default     = "10.20.1.0/24"
}

variable "app_subnet_prefix" {
  description = "CIDR prefix for the Function App VNet-integration subnet"
  type        = string
  default     = "10.20.2.0/24"
}

variable "tags" {
  description = "Common resource tags"
  type        = map(string)
  default     = {}
}
