variable "name" {
  description = "Name of the AML compute cluster, e.g. cpu-cluster-dev"
  type        = string
}

variable "location" {
  description = "Azure region for the compute cluster (must match the workspace region)"
  type        = string
}

variable "aml_workspace_id" {
  description = "Resource ID of the parent Azure ML workspace"
  type        = string
}

variable "subnet_id" {
  description = "Resource ID of the subnet the compute cluster's nodes are attached to (optional)"
  type        = string
  default     = null
}

variable "vm_size" {
  description = "VM SKU for cluster nodes, e.g. Standard_DS3_v2"
  type        = string
  default     = "Standard_DS3_v2"
}

variable "vm_priority" {
  description = "VM priority: Dedicated or LowPriority"
  type        = string
  default     = "Dedicated"
}

variable "min_node_count" {
  description = "Minimum number of nodes (0 allows scale-to-zero)"
  type        = number
  default     = 0
}

variable "max_node_count" {
  description = "Maximum number of nodes"
  type        = number
  default     = 2
}

variable "scale_down_idle_duration" {
  description = "ISO 8601 duration of idle time before scaling down a node, e.g. PT30M"
  type        = string
  default     = "PT30M"
}

variable "tags" {
  description = "Common resource tags"
  type        = map(string)
  default     = {}
}
