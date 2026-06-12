output "vnet_id" {
  description = "Resource ID of the virtual network"
  value       = azurerm_virtual_network.this.id
}

output "aml_subnet_id" {
  description = "Resource ID of the AML compute/private-endpoint subnet"
  value       = azurerm_subnet.aml.id
}

output "app_subnet_id" {
  description = "Resource ID of the Function App subnet"
  value       = azurerm_subnet.app.id
}
