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

# Free resource group
resource "azurerm_resource_group" "rg" {
  name     = "flask-free-rg"
  location = "Central India"
}

# Free App Service Plan (F1 = Free)
resource "azurerm_service_plan" "plan" {
  name                = "flask-free-plan"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  os_type             = "Linux"
  sku_name            = "F1" # Free tier
}

# Free Web App (pulls image from GitHub Container Registry)
resource "azurerm_linux_web_app" "app" {
  name                = "flask-free-webapp-${random_integer.suffix.result}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  service_plan_id     = azurerm_service_plan.plan.id

  site_config {
    application_stack {
      docker_image     = "ghcr.io/Muneesh08/flask-app"
      docker_image_tag = "latest"
    }
  }

  app_settings = {
    WEBSITES_PORT = "5000"
  }

  identity {
    type = "SystemAssigned"
  }
}

# Generate random suffix for unique name
resource "random_integer" "suffix" {
  min = 1000
  max = 9999
}

output "webapp_url" {
  value = azurerm_linux_web_app.app.default_hostname
}

