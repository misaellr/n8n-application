controller:
  service:
    type: LoadBalancer
    annotations:
      service.beta.kubernetes.io/aws-load-balancer-type: "nlb"
      service.beta.kubernetes.io/aws-load-balancer-eip-allocations: "${nlb_eips}"
      service.beta.kubernetes.io/aws-load-balancer-subnets: "${nlb_subnets}"
