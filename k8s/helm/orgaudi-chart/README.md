# OrgAudi Helm Chart

Helm chart para deployment de OrgAudi em Kubernetes.

## Prerequisitos

- Kubernetes 1.20+
- Helm 3.0+
- Cert-Manager (para HTTPS)
- Nginx Ingress Controller

## Instalação

### 1. Adicionar Helm repository

```bash
helm repo add orgaudi https://charts.orgaudi.com
helm repo update
```

### 2. Criar valores customizados

```bash
cp values.yaml my-values.yaml
# Editar my-values.yaml com suas configurações
```

### 3. Instalar release

```bash
helm install orgaudi orgaudi/orgaudi-chart -f my-values.yaml -n orgaudi --create-namespace
```

## Configuração

### Domínio

```yaml
global:
  domain: orgaudi.exemplo.com.br
```

### Réplicas

```yaml
backend:
  replicaCount: 3

frontend:
  replicaCount: 2
```

### Autoscaling

```yaml
autoscaling:
  enabled: true
  backend:
    minReplicas: 3
    maxReplicas: 10
    targetCPUUtilizationPercentage: 70
```

## Deploy

### DEV (Minikube/Kind)

```bash
helm install orgaudi . -f values-dev.yaml -n orgaudi
```

### STAGING

```bash
helm install orgaudi . -f values-staging.yaml -n orgaudi
```

### PRODUCTION

```bash
helm install orgaudi . -f values-prod.yaml -n orgaudi
```

## Verificar Status

```bash
kubectl get pods -n orgaudi
kubectl logs -n orgaudi deployment/orgaudi-backend
kubectl port-forward -n orgaudi svc/orgaudi-frontend 8080:80
```

## Upgrade

```bash
helm upgrade orgaudi orgaudi/orgaudi-chart -f my-values.yaml -n orgaudi
```

## Uninstall

```bash
helm uninstall orgaudi -n orgaudi
```
