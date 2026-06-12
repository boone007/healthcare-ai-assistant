output "id" {
  description = "Resource ID of the Application Insights instance"
  value       = azurerm_application_insights.this.id
}

output "name" {
  description = "Name of the Application Insights instance"
  value       = azurerm_application_insights.this.name
}

output "instrumentation_key" {
  description = "Instrumentation key for the Application Insights instance"
  value       = azurerm_application_insights.this.instrumentation_key
  sensitive   = true
}

output "connection_string" {
  description = "Connection string for the Application Insights instance"
  value       = azurerm_application_insights.this.connection_string
  sensitive   = true
}

output "log_analytics_workspace_id" {
  description = "Resource ID of the underlying Log Analytics workspace"
  value       = azurerm_log_analytics_workspace.this.id
}
