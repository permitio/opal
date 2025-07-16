#!/bin/bash

# Demo script for Single-Topic Multi-Tenant OPAL
# Uses remote policy repo with single-topic-multi-tenant subfolder

set -e

echo "🚀 Starting Single-Topic Multi-Tenant OPAL Demo..."
echo "📋 Policies from official repo: github.com/permitio/opal-example-policy-repo"
echo "📁 Subfolder: single-topic-multi-tenant"

# Stop existing containers
echo "🧹 Cleaning up existing containers..."
docker-compose -f docker-compose-single-topic-multi-tenant.yml down -v

# Start services
echo "🆙 Starting OPAL services..."
docker-compose -f docker-compose-single-topic-multi-tenant.yml up -d

# Wait for startup
echo "⏳ Waiting for services to start..."
sleep 15

# Check service status
echo "🔍 Checking service status..."
for i in {1..30}; do
    if curl -s http://localhost:7002/healthcheck > /dev/null 2>&1; then
        echo "✅ OPAL Server is ready"
        break
    fi
    echo "⏳ Waiting for OPAL Server... ($i/30)"
    sleep 2
done

# Check OPA
for i in {1..30}; do
    if curl -s http://localhost:8181/health > /dev/null 2>&1; then
        echo "✅ OPA is ready"
        break
    fi
    echo "⏳ Waiting for OPA... ($i/30)"
    sleep 2
done

echo ""
echo "🎯 Configuring External Data Sources for Multi-Tenant..."

# Add data for Tenant 1 (TechCorp company)
echo "📊 Adding data for Tenant 1 (TechCorp)..."
curl -X POST http://localhost:7002/data/config \
  -H "Content-Type: application/json" \
  -d '{
    "entries": [{
      "url": "http://example_external_data_provider:80/acl/tenant1",
      "topics": ["tenant_data"],
      "dst_path": "/acl/tenant1"
    }],
    "reason": "Load tenant1 data via single topic - DEMO"
  }'

# Add data for Tenant 2 (DataFlow company)
echo "📊 Adding data for Tenant 2 (DataFlow)..."
curl -X POST http://localhost:7002/data/config \
  -H "Content-Type: application/json" \
  -d '{
    "entries": [{
      "url": "http://example_external_data_provider:80/acl/tenant2",
      "topics": ["tenant_data"],
      "dst_path": "/acl/tenant2"
    }],
    "reason": "Load tenant2 data via single topic - NO RESTART!"
  }'

echo "⏳ Waiting for configuration propagation..."
sleep 10

echo ""
echo "📋 External Data Sources status:"
curl -s http://localhost:7002/data/config | jq '.'

echo ""
echo "🧪 Testing authorization queries..."

echo ""
echo "🏢 TENANT 1 (TechCorp) - OPA on port 8181:"
echo "👤 alice (admin) -> documents/read:"
curl -s -X POST http://localhost:8181/v1/data/multi_tenant_rbac/allow \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "user": "alice",
      "action": "read",
      "resource": "documents"
    }
  }' | jq '.result'

echo "👤 bob (editor) -> documents/edit:"
curl -s -X POST http://localhost:8181/v1/data/multi_tenant_rbac/allow \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "user": "bob",
      "action": "edit",
      "resource": "documents"
    }
  }' | jq '.result'

echo ""
echo "🏢 TENANT 2 (DataFlow) - Same OPA, different data:"
echo "👤 charlie (viewer) -> files/read:"
curl -s -X POST http://localhost:8181/v1/data/multi_tenant_rbac/allow \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "user": "charlie",
      "action": "read",
      "resource": "files"
    }
  }' | jq '.result'

echo "👤 diana (editor) -> files/edit:"
curl -s -X POST http://localhost:8181/v1/data/multi_tenant_rbac/allow \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "user": "diana",
      "action": "edit",
      "resource": "files"
    }
  }' | jq '.result'

echo ""
echo "🔍 Verifying data isolation:"
echo "📊 All data in OPA (isolated by paths):"
curl -s http://localhost:8181/v1/data/acl | jq '.'

echo ""
echo "📊 Data for tenant1 only:"
curl -s http://localhost:8181/v1/data/acl/tenant1 | jq '.'

echo ""
echo "📊 Data for tenant2 only:"
curl -s http://localhost:8181/v1/data/acl/tenant2 | jq '.'

echo ""
echo "✅ Demo completed!"
echo "🎉 Single-Topic Multi-Tenant OPAL works with remote policy repo!"
echo ""
echo "📖 Key features:"
echo "   • 1 topic (tenant_data) for all tenants"
echo "   • N external data sources for N tenants"
echo "   • Data isolation through OPA paths (/acl/tenant1, /acl/tenant2)"
echo "   • Policies from official repo subfolder: single-topic-multi-tenant"
echo "   • No restarts needed when adding new tenants"
echo "   • Policies compatible with older OPA versions"
