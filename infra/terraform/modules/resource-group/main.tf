# Resource Group module
#
# Creates the single resource group that scopes all environment resources
# for the AI-Powered Personalized Healthcare Assistant.

resource "azurerm_resource_group" "this" {
  name     = var.name
  location = var.location
  tags     = var.tags
}
