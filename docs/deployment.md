# Deployment Guide

This guide covers deploying ContextDock to production environments.

## Table of Contents

- [Production Requirements](#production-requirements)
- [Docker Deployment](#docker-deployment)
- [Kubernetes Deployment](#kubernetes-deployment)
- [TLS/SSL Setup](#tlsssl-setup)
- [Environment Configuration](#environment-configuration)
- [Monitoring & Alerts](#monitoring--alerts)
- [Backup & Recovery](#backup--recovery)
- [Security Best Practices](#security-best-practices)
- [Scaling](#scaling)

## Production Requirements

### Infrastructure

- **Compute**: 4 CPU cores, 8GB RAM minimum (per API instance)
- **Database**: PostgreSQL 15+ (managed service recommended)
- **Cache**: Redis 7+ (managed service recommended)
- **Vector DB**: Qdrant (self-hosted or cloud)
- **Storage**: 100GB+ for application data
- **Network**: Load balancer with TLS termination

### External Services

- **OpenAI API**: Active API key with sufficient quota
- **OAuth Apps**: Configured for each connector (Slack, Jira, etc.)

## Docker Deployment

### Quick Start with Docker Compose

1. **Clone repository**
   ```bash
   git clone https://github.com/saurabhkashyap259/ContextDock.git
   cd ContextDock
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env.production
   # Edit .env.production with production values
   ```

3. **Start services**
   ```bash
   docker-compose -f docker-compose.prod.yml up -d
   ```

4. **Run migrations**
   ```bash
   docker-compose -f docker-compose.prod.yml exec api alembic upgrade head
   ```

5. **Verify deployment**
   ```bash
   curl https://your-domain.com/health
   ```

### Docker Compose Configuration

Example `docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  api:
    image: contextdock/api:latest
    restart: always
    env_file: .env.production
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - redis
      - qdrant
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  worker:
    image: contextdock/api:latest
    restart: always
    command: celery -A src.workers.celery_app worker --loglevel=info --concurrency=4
    env_file: .env.production
    depends_on:
      - postgres
      - redis
      - qdrant
    deploy:
      replicas: 2
      resources:
        limits:
          cpus: '2'
          memory: 4G

  beat:
    image: contextdock/api:latest
    restart: always
    command: celery -A src.workers.celery_app beat --loglevel=info
    env_file: .env.production
    depends_on:
      - redis
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M

  postgres:
    image: postgres:15-alpine
    restart: always
    environment:
      POSTGRES_DB: contextdock
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    deploy:
      resources:
        limits:
          memory: 2G

  redis:
    image: redis:7-alpine
    restart: always
    command: redis-server --maxmemory 1gb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    deploy:
      resources:
        limits:
          memory: 1G

  qdrant:
    image: qdrant/qdrant:latest
    restart: always
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G

  nginx:
    image: nginx:alpine
    restart: always
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - api

volumes:
  postgres_data:
  redis_data:
  qdrant_data:
```

## Kubernetes Deployment

### Prerequisites

- Kubernetes cluster (1.25+)
- kubectl configured
- Helm 3+

### Namespace Setup

```bash
kubectl create namespace contextdock
```

### Secrets

Create secret for sensitive values:

```bash
kubectl create secret generic contextdock-secrets \
  --from-literal=database-url='postgresql://...' \
  --from-literal=redis-url='redis://...' \
  --from-literal=openai-api-key='sk-...' \
  --from-literal=slack-client-secret='...' \
  -n contextdock
```

### Deployment Manifests

**API Deployment** (`k8s/api-deployment.yaml`):

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: contextdock-api
  namespace: contextdock
spec:
  replicas: 3
  selector:
    matchLabels:
      app: contextdock-api
  template:
    metadata:
      labels:
        app: contextdock-api
    spec:
      containers:
      - name: api
        image: contextdock/api:v1.0.0
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: contextdock-secrets
              key: database-url
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: contextdock-secrets
              key: redis-url
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: contextdock-secrets
              key: openai-api-key
        resources:
          requests:
            cpu: 1000m
            memory: 2Gi
          limits:
            cpu: 2000m
            memory: 4Gi
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: contextdock-api
  namespace: contextdock
spec:
  selector:
    app: contextdock-api
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8000
  type: LoadBalancer
```

**Worker Deployment** (`k8s/worker-deployment.yaml`):

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: contextdock-worker
  namespace: contextdock
spec:
  replicas: 3
  selector:
    matchLabels:
      app: contextdock-worker
  template:
    metadata:
      labels:
        app: contextdock-worker
    spec:
      containers:
      - name: worker
        image: contextdock/api:v1.0.0
        command: ["celery"]
        args: ["-A", "src.workers.celery_app", "worker", "--loglevel=info", "--concurrency=4"]
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: contextdock-secrets
              key: database-url
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: contextdock-secrets
              key: redis-url
        resources:
          requests:
            cpu: 1000m
            memory: 2Gi
          limits:
            cpu: 2000m
            memory: 4Gi
```

**Apply manifests:**

```bash
kubectl apply -f k8s/
```

### Horizontal Pod Autoscaling

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: contextdock-api-hpa
  namespace: contextdock
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: contextdock-api
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

## TLS/SSL Setup

### Using Nginx as Reverse Proxy

**nginx.conf:**

```nginx
# /etc/nginx/nginx.conf

events {
    worker_connections 1024;
}

http {
    upstream contextdock_api {
        server api:8000;
    }

    # Redirect HTTP to HTTPS
    server {
        listen 80;
        server_name your-domain.com;
        return 301 https://$server_name$request_uri;
    }

    # HTTPS server
    server {
        listen 443 ssl http2;
        server_name your-domain.com;

        # TLS certificates (FR-036: TLS via nginx reverse proxy)
        ssl_certificate /etc/nginx/ssl/cert.pem;
        ssl_certificate_key /etc/nginx/ssl/key.pem;
        
        # Modern TLS configuration
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256';
        ssl_prefer_server_ciphers off;
        
        # Security headers
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-XSS-Protection "1; mode=block" always;

        # Proxy settings
        location / {
            proxy_pass http://contextdock_api;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            
            # WebSocket support (for streaming)
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            
            # Timeouts
            proxy_connect_timeout 60s;
            proxy_send_timeout 60s;
            proxy_read_timeout 60s;
        }
        
        # Metrics endpoint (internal only)
        location /metrics {
            proxy_pass http://contextdock_api/metrics;
            allow 10.0.0.0/8;  # Internal network only
            deny all;
        }
    }
}
```

### Let's Encrypt with Certbot

```bash
# Install certbot
apt-get install certbot python3-certbot-nginx

# Obtain certificate
certbot --nginx -d your-domain.com

# Auto-renewal (cron job)
0 0 * * * certbot renew --quiet
```

## Environment Configuration

### Required Environment Variables

```bash
# Application
ENVIRONMENT=production
LOG_LEVEL=INFO
SECRET_KEY=your-secret-key-generate-with-openssl

# Database
DATABASE_URL=postgresql://user:password@postgres-host:5432/contextdock
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10

# Redis
REDIS_URL=redis://redis-host:6379/0

# Qdrant
QDRANT_URL=https://qdrant-host:6333
QDRANT_API_KEY=your-qdrant-api-key

# OpenAI
OPENAI_API_KEY=sk-your-openai-api-key
OPENAI_ORG_ID=org-your-org-id

# OAuth Credentials
SLACK_CLIENT_ID=your-slack-client-id
SLACK_CLIENT_SECRET=your-slack-client-secret
SLACK_REDIRECT_URI=https://your-domain.com/oauth/slack/callback

JIRA_CLIENT_ID=your-jira-client-id
JIRA_CLIENT_SECRET=your-jira-client-secret
JIRA_REDIRECT_URI=https://your-domain.com/oauth/jira/callback

GITHUB_CLIENT_ID=your-github-client-id
GITHUB_CLIENT_SECRET=your-github-client-secret
GITHUB_REDIRECT_URI=https://your-domain.com/oauth/github/callback

# Monitoring
SENTRY_DSN=https://your-sentry-dsn
PROMETHEUS_ENABLED=true

# Security
ALLOWED_ORIGINS=https://your-domain.com
CORS_ENABLED=true
```

### Generate Secret Key

```bash
openssl rand -hex 32
```

## Monitoring & Alerts

### Prometheus Setup

**prometheus.yml:**

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'contextdock'
    static_configs:
      - targets: ['api:8000']
    metrics_path: '/metrics'
```

### Grafana Dashboard

Import dashboard from `monitoring/grafana-dashboard.json` or create custom:

**Key Metrics to Monitor:**
- Request rate & latency (p50, p95, p99)
- Query latency by workspace
- Sync success/failure rates
- Circuit breaker state
- Database connection pool usage
- Redis cache hit rate
- Celery queue depth
- Error rates

### Alerting Rules

**prometheus-alerts.yml:**

```yaml
groups:
  - name: contextdock
    interval: 30s
    rules:
      - alert: HighErrorRate
        expr: rate(contextdock_requests_total{status=~"5.."}[5m]) > 0.05
        for: 5m
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value }} errors/sec"
      
      - alert: HighQueryLatency
        expr: histogram_quantile(0.95, rate(contextdock_query_latency_seconds_bucket[5m])) > 15
        for: 5m
        annotations:
          summary: "Query latency p95 > 15s"
      
      - alert: CircuitBreakerOpen
        expr: contextdock_circuit_breaker_state{service="qdrant"} == 1
        for: 1m
        annotations:
          summary: "Circuit breaker open for Qdrant"
      
      - alert: SyncFailures
        expr: rate(contextdock_sync_failure_total[10m]) > 0.1
        for: 5m
        annotations:
          summary: "High sync failure rate"
```

## Backup & Recovery

### Database Backup

```bash
# Daily backup script
#!/bin/bash
BACKUP_DIR=/backups/postgres
DATE=$(date +%Y%m%d_%H%M%S)
pg_dump $DATABASE_URL > $BACKUP_DIR/contextdock_$DATE.sql
gzip $BACKUP_DIR/contextdock_$DATE.sql

# Keep last 30 days
find $BACKUP_DIR -name "*.sql.gz" -mtime +30 -delete
```

### Qdrant Backup

```bash
# Backup Qdrant storage
tar -czf qdrant_backup_$(date +%Y%m%d).tar.gz /path/to/qdrant/storage
```

### Restore Process

```bash
# Restore database
gunzip contextdock_backup.sql.gz
psql $DATABASE_URL < contextdock_backup.sql

# Restore Qdrant
tar -xzf qdrant_backup.tar.gz -C /path/to/qdrant/
```

## Security Best Practices

### Data Privacy (FR-039)

**ContextDock does NOT use customer data for training AI models.**

- Set OpenAI API parameter: `training_opt_out=True`
- Document content stays in your infrastructure
- Embeddings generated on-demand, not shared
- No telemetry sent to third parties

### Access Control

- Use strong passwords (min 12 characters)
- Enable MFA for admin accounts
- Rotate API keys quarterly
- Use least-privilege principle for OAuth scopes

### Network Security

- Whitelist IP ranges for admin endpoints
- Use VPN for internal services
- Enable DDoS protection
- Rate limit public endpoints

### Application Security

- Keep dependencies updated (`pip-audit`)
- Scan for vulnerabilities (`safety check`)
- Use environment variables for secrets (never hardcode)
- Enable audit logging
- Implement request rate limiting

## Scaling

### Horizontal Scaling

**API Servers:**
- Scale based on CPU (70% threshold)
- 3-10 replicas recommended
- Use load balancer with session affinity (if needed)

**Celery Workers:**
- Scale based on queue depth
- 2-5 workers per connector type
- Separate queues for different priorities

### Vertical Scaling

**Database:**
- Start: 2 CPUs, 4GB RAM
- Medium: 4 CPUs, 16GB RAM
- Large: 8+ CPUs, 32GB+ RAM

**Qdrant:**
- Start: 2 CPUs, 4GB RAM
- Scale based on index size (1GB RAM per 1M vectors)

### Caching Strategy

- Redis for identity resolution (1hr TTL)
- CDN for static assets
- Application-level caching for expensive queries

## Troubleshooting

### Common Issues

**High latency:**
- Check database connection pool settings
- Verify Qdrant performance
- Review slow query logs

**Memory leaks:**
- Monitor memory usage over time
- Check for unclosed database connections
- Review worker memory limits

**Sync failures:**
- Check OAuth token expiration
- Verify connector rate limits
- Review error logs

### Health Check

```bash
curl https://your-domain.com/health | jq .
```

Expected response:
```json
{
  "status": "healthy",
  "services": {
    "database": {"status": "up", "latency_ms": 5.2},
    "redis": {"status": "up", "latency_ms": 1.1},
    "qdrant": {"status": "up", "latency_ms": 8.5}
  }
}
```

## Maintenance

### Database Maintenance

```sql
-- Vacuum and analyze
VACUUM ANALYZE;

-- Reindex
REINDEX DATABASE contextdock;

-- Check table sizes
SELECT 
  schemaname, 
  tablename, 
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

### Log Rotation

Configure logrotate:

```
/var/log/contextdock/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 0640 contextdock contextdock
    sharedscripts
}
```

## Support

For production issues:
- Check logs: `kubectl logs -f deployment/contextdock-api`
- Review metrics: Grafana dashboard
- Contact: support@contextdock.com
