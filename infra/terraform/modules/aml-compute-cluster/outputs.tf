output "id" {
  description = "Resource ID of the AML compute cluster"
  value       = azurerm_machine_learning_compute_cluster.this.id
}

output "name" {
  description = "Name of the AML compute cluster"
  value       = azurerm_machine_learning_compute_cluster.this.name
}
