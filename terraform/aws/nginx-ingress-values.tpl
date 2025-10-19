controller:
  service:
    type: LoadBalancer
    annotations:
      service.beta.kubernetes.io/aws-load-balancer-type: "nlb"
      service.beta.kubernetes.io/aws-load-balancer-subnets: "${nlb_subnets}"
      # AWS will automatically create and manage EIPs for the NLB
      # This prevents orphaned EIPs when deployments fail
