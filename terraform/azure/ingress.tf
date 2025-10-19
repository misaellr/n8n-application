########################################
# NGINX Ingress Controller
# Deployed via Helm
########################################

# NGINX Ingress Controller Helm Release
resource "helm_release" "nginx_ingress" {
  count = var.enable_nginx_ingress ? 1 : 0

  name       = "ingress-nginx"
  repository = "https://kubernetes.github.io/ingress-nginx"
  chart      = "ingress-nginx"
  namespace  = "ingress-nginx"
  version    = "4.10.0"

  create_namespace = true
  timeout          = 600
  wait             = true

  values = [
    templatefile("${path.module}/nginx-ingress-values.tpl", {
      use_static_ip   = var.use_static_ip
      loadbalancer_ip = var.use_static_ip ? azurerm_public_ip.lb[0].ip_address : ""
      resource_group  = azurerm_resource_group.main.name
    })
  ]

  depends_on = [
    azurerm_kubernetes_cluster.main,
    # Wait for role assignment if using static IP
    azurerm_role_assignment.aks_network_contributor
  ]
}

########################################
# Cert-Manager (Optional)
# For automatic TLS certificate management
########################################

# Cert-Manager Namespace
resource "kubernetes_namespace" "cert_manager" {
  count = var.enable_cert_manager ? 1 : 0

  metadata {
    name = "cert-manager"
  }

  depends_on = [azurerm_kubernetes_cluster.main]
}

# Cert-Manager Helm Release
resource "helm_release" "cert_manager" {
  count = var.enable_cert_manager ? 1 : 0

  name       = "cert-manager"
  repository = "https://charts.jetstack.io"
  chart      = "cert-manager"
  namespace  = kubernetes_namespace.cert_manager[0].metadata[0].name
  version    = "v1.14.4"

  set {
    name  = "installCRDs"
    value = "true"
  }

  set {
    name  = "global.leaderElection.namespace"
    value = "cert-manager"
  }

  depends_on = [
    azurerm_kubernetes_cluster.main,
    kubernetes_namespace.cert_manager
  ]
}

# ClusterIssuer for Let's Encrypt (if cert-manager is enabled)
resource "kubernetes_manifest" "letsencrypt_issuer" {
  count = var.enable_cert_manager ? 1 : 0

  manifest = {
    apiVersion = "cert-manager.io/v1"
    kind       = "ClusterIssuer"
    metadata = {
      name = "letsencrypt-prod"
    }
    spec = {
      acme = {
        server = "https://acme-v02.api.letsencrypt.org/directory"
        email  = "admin@${var.n8n_host}"
        privateKeySecretRef = {
          name = "letsencrypt-prod"
        }
        solvers = [
          {
            http01 = {
              ingress = {
                class = "nginx"
              }
            }
          }
        ]
      }
    }
  }

  depends_on = [helm_release.cert_manager]
}
