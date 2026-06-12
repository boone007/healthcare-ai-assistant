output "id" {
  description = "Resource ID of the Key Vault"
  value       = azurerm_key_vault.this.id
}

output "name" {
  description = "Name of the Key Vault"
  value       = azurerm_key_vault.this.name
}

output "vault_uri" {
  description = "URI of the Key Vault, used by app configuration (e.g. KEY_VAULT_URI)"
  value       = azurerm_key_vault.this.vault_uri
}
