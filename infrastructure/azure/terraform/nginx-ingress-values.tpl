controller:
  # Service configuration for Azure Load Balancer
  service:
    type: LoadBalancer
    annotations:
      # Use the pre-allocated public IP
      service.beta.kubernetes.io/azure-load-balancer-resource-group: "${resource_group}"
      # Specify the static IP address
      service.beta.kubernetes.io/azure-pip-name: "${loadbalancer_ip}"
      # Health probe configuration
      service.beta.kubernetes.io/azure-load-balancer-health-probe-request-path: "/healthz"

    # Specify the static IP (Azure requires this)
    loadBalancerIP: "${loadbalancer_ip}"

    # External traffic policy
    externalTrafficPolicy: "Local"

    # Enable HTTP and HTTPS
    enableHttp: true
    enableHttps: true

  # Resource limits and requests
  resources:
    limits:
      cpu: 200m
      memory: 256Mi
    requests:
      cpu: 100m
      memory: 128Mi

  # Replica configuration
  replicaCount: 2

  # Pod anti-affinity for high availability
  affinity:
    podAntiAffinity:
      preferredDuringSchedulingIgnoredDuringExecution:
        - weight: 100
          podAffinityTerm:
            labelSelector:
              matchExpressions:
                - key: app.kubernetes.io/name
                  operator: In
                  values:
                    - ingress-nginx
                - key: app.kubernetes.io/component
                  operator: In
                  values:
                    - controller
            topologyKey: kubernetes.io/hostname

  # Autoscaling configuration
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 5
    targetCPUUtilizationPercentage: 80
    targetMemoryUtilizationPercentage: 80

  # Metrics
  metrics:
    enabled: true
    serviceMonitor:
      enabled: false

  # Pod Disruption Budget
  podDisruptionBudget:
    enabled: true
    minAvailable: 1

  # Configuration for ingress controller
  config:
    # Proxy settings
    proxy-body-size: "100m"
    proxy-buffer-size: "8k"

    # SSL settings
    ssl-protocols: "TLSv1.2 TLSv1.3"
    ssl-ciphers: "ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384"

    # Performance tuning
    worker-processes: "auto"
    max-worker-connections: "16384"

    # Logging
    log-format-upstream: '$remote_addr - $remote_user [$time_local] "$request" $status $body_bytes_sent "$http_referer" "$http_user_agent" $request_length $request_time [$proxy_upstream_name] [$proxy_alternative_upstream_name] $upstream_addr $upstream_response_length $upstream_response_time $upstream_status $req_id'

    # Security headers
    enable-ocsp: "true"
    hsts: "true"
    hsts-include-subdomains: "true"
    hsts-max-age: "31536000"

# Default backend
defaultBackend:
  enabled: true
  replicaCount: 1
  resources:
    limits:
      cpu: 50m
      memory: 64Mi
    requests:
      cpu: 25m
      memory: 32Mi

# RBAC
rbac:
  create: true

# Service Account
serviceAccount:
  create: true

# Admission webhooks
admissionWebhooks:
  enabled: true
  patch:
    enabled: true
