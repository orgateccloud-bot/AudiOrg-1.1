# Kubernetes Deployment para OrgAudi

Este diretório contém configurações de Kubernetes e Helm para deployment de OrgAudi.

## Estrutura

```
k8s/
├── helm/
│   └── orgaudi-chart/       # Helm chart principal
│       ├── Chart.yaml
│       ├── values.yaml
│       ├── values-dev.yaml
│       ├── values-staging.yaml
│       ├── values-prod.yaml
│       ├── templates/
│       │   ├── deployment-backend.yaml
│       │   ├── deployment-frontend.yaml
│       │   ├── service-backend.yaml
│       │   ├── service-frontend.yaml
│       │   ├── ingress.yaml
│       │   ├── hpa.yaml
│       │   ├── configmap.yaml
│       │   ├── networkpolicy.yaml
│       │   └── _helpers.tpl
│       └── README.md
├── kustomize/               # Kustomize overlays (alternativo)
│   ├── base/
│   ├── overlays/dev/
│   ├── overlays/staging/
│   └── overlays/prod/
└── README.md
```

## Guia Rápido

### Deploy com Helm

```bash
# Dev (Minikube)
helm install orgaudi helm/orgaudi-chart --values helm/orgaudi-chart/values-dev.yaml

# Staging
helm install orgaudi helm/orgaudi-chart --values helm/orgaudi-chart/values-staging.yaml

# Production
helm install orgaudi helm/orgaudi-chart --values helm/orgaudi-chart/values-prod.yaml -n orgaudi
```

### Deploy com Kustomize

```bash
kubectl apply -k kustomize/overlays/dev/
kubectl apply -k kustomize/overlays/prod/
```

## Componentes

### Backend (FastAPI)
- **Replicas**: 3 (prod)
- **Port**: 8082
- **Resources**: 512Mi mem / 250m cpu (request) → 2Gi / 1000m (limit)
- **Healthcheck**: `/health`

### Frontend (React)
- **Replicas**: 2 (prod)
- **Port**: 80
- **Resources**: 256Mi mem / 100m cpu (request) → 1Gi / 500m (limit)

### Database (PostgreSQL)
- **Replicas**: 1 primary
- **Port**: 5432
- **Resources**: 1Gi mem / 500m cpu (request) → 4Gi / 2000m (limit)

### Cache (Redis)
- **Port**: 6379
- **Resources**: 256Mi mem / 100m cpu (request) → 512Mi / 500m (limit)

### Vector DB (Qdrant)
- **Port**: 6333
- **Resources**: 2Gi mem / 1000m cpu (request) → 8Gi / 4000m (limit)

## Monitoring

```bash
# Prometheus metrics
kubectl port-forward -n orgaudi svc/orgaudi-backend 9090:9090

# Grafana dashboards
kubectl port-forward -n orgaudi svc/prometheus-grafana 3000:80
```

## Troubleshooting

```bash
# Logs
kubectl logs -n orgaudi -l component=backend
kubectl logs -n orgaudi -l component=frontend

# Events
kubectl get events -n orgaudi --sort-by='.lastTimestamp'

# Describe pod
kubectl describe pod -n orgaudi <pod-name>

# Port forward para debug
kubectl port-forward -n orgaudi svc/orgaudi-backend 8082:8082
```

## Security

- Network policies: Restringem tráfego entre pods
- Security context: Rodam como non-root (uid 1000)
- Pod security policy: Ativada
- TLS: Automático via cert-manager + Let's Encrypt

## Escalabilidade

- HPA: Autoscaling baseado em CPU/memory
- Backend: 3-10 replicas
- Frontend: 2-5 replicas
- PostgreSQL: Replica set (failover automático)
