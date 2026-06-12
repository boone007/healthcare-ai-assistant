# Azure ML Compute Cluster module
#
# Provisions an autoscaling AML compute cluster used for training,
# hyperparameter sweeps, and responsible AI jobs.

resource "azurerm_machine_learning_compute_cluster" "this" {
  name                          = var.name
  location                      = var.location
  vm_priority                   = var.vm_priority
  vm_size                       = var.vm_size
  machine_learning_workspace_id = var.aml_workspace_id

  scale_settings {
    min_node_count                   = var.min_node_count
    max_node_count                   = var.max_node_count
    scale_down_nodes_after_idle_duration = var.scale_down_idle_duration
  }

  subnet_resource_id = var.subnet_id

  identity {
    type = "SystemAssigned"
  }

  tags = var.tags
}
