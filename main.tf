terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~>3.100.0"
    }
  }

  backend "local" {
    path = "terraform.tfstate"
  }
}

provider "azurerm" {
  features {}
}

# Resource Group
resource "azurerm_resource_group" "rg" {
  name     = "flask-rg"
  location = "Central India"
}

# App Service Plan
resource "azurerm_service_plan" "plan" {
  name                = "flask-service-plan"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  os_type             = "Linux"
  sku_name            = "B1"
}

# Azure Container Registry
resource "azurerm_container_registry" "acr" {
  name                = "flaskacr12345"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  sku                 = "Basic"
  admin_enabled       = true
}

# Web App (connects to ACR image)
resource "azurerm_linux_web_app" "app" {
  name                = "flask-web-app-12345"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  service_plan_id     = azurerm_service_plan.plan.id

  site_config {
    application_stack {
      docker_image     = "${azurerm_container_registry.acr.login_server}/flask-app"
      docker_image_tag = "latest"
    }
  }

  app_settings = {
    WEBSITES_PORT = "5000"
    DOCKER_REGISTRY_SERVER_URL      = "https://${azurerm_container_registry.acr.login_server}"
    DOCKER_REGISTRY_SERVER_USERNAME = azurerm_container_registry.acr.admin_username
    DOCKER_REGISTRY_SERVER_PASSWORD = azurerm_container_registry.acr.admin_password
  }
}

output "webapp_url" {
  value = azurerm_linux_web_app.app.default_hostname
}
