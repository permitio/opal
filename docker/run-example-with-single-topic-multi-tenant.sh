#!/bin/bash

# Skrypt demo dla Single-Topic Multi-Tenant OPAL
# Używa zdalnego repo polityk z subfolder single-topic-multi-tenant

set -e

echo "🚀 Uruchamianie Single-Topic Multi-Tenant OPAL Demo..."
echo "📋 Polityki z zdalnego repo: github.com/plduser/opal-example-policy-repo"
echo "📁 Subfolder: single-topic-multi-tenant"

# Zatrzymaj istniejące kontenery
echo "🧹 Czyszczenie istniejących kontenerów..."
docker-compose -f docker-compose-single-topic-multi-tenant.yml down -v

# Uruchom usługi
echo "🆙 Uruchamianie usług OPAL..."
docker-compose -f docker-compose-single-topic-multi-tenant.yml up -d

# Poczekaj na uruchomienie
echo "⏳ Oczekiwanie na uruchomienie usług..."
sleep 15

# Sprawdź status usług
echo "🔍 Sprawdzanie statusu usług..."
for i in {1..30}; do
    if curl -s http://localhost:7002/healthcheck > /dev/null 2>&1; then
        echo "✅ OPAL Server jest gotowy"
        break
    fi
    echo "⏳ Oczekiwanie na OPAL Server... ($i/30)"
    sleep 2
done

# Sprawdź OPA
for i in {1..30}; do
    if curl -s http://localhost:8181/health > /dev/null 2>&1; then
        echo "✅ OPA jest gotowe"
        break
    fi
    echo "⏳ Oczekiwanie na OPA... ($i/30)"
    sleep 2
done

echo ""
echo "🎯 Konfiguracja External Data Sources dla Multi-Tenant..."

# Dodaj dane dla Tenant 1 (firma TechCorp)
echo "📊 Dodawanie danych dla Tenant 1 (TechCorp)..."
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

# Dodaj dane dla Tenant 2 (firma DataFlow)  
echo "📊 Dodawanie danych dla Tenant 2 (DataFlow)..."
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

echo "⏳ Oczekiwanie na propagację konfiguracji..."
sleep 10

echo ""
echo "📋 Stan External Data Sources:"
curl -s http://localhost:7002/data/config | jq '.'

echo ""
echo "🧪 Testowanie zapytań autoryzacyjnych..."

echo ""
echo "🏢 TENANT 1 (TechCorp) - OPA na porcie 8181:"
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
echo "🏢 TENANT 2 (DataFlow) - Ten sam OPA, różne dane:"
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
echo "🔍 Weryfikacja izolacji danych:"
echo "📊 Wszystkie dane w OPA (izolowane przez ścieżki):"
curl -s http://localhost:8181/v1/data/acl | jq '.'

echo ""
echo "📊 Dane tylko dla tenant1:" 
curl -s http://localhost:8181/v1/data/acl/tenant1 | jq '.'

echo ""
echo "📊 Dane tylko dla tenant2:" 
curl -s http://localhost:8181/v1/data/acl/tenant2 | jq '.'

echo ""
echo "✅ Demo zakończone!"
echo "🎉 Single-Topic Multi-Tenant OPAL działa z zdalnym repo polityk!"
echo ""
echo "📖 Kluczowe cechy:"
echo "   • 1 temat (tenant_data) dla wszystkich tenantów"
echo "   • N external data sources dla N tenantów"  
echo "   • Izolacja danych przez ścieżki OPA (/acl/tenant1, /acl/tenant2)"
echo "   • Polityki z zdalnego repo subfolder: single-topic-multi-tenant"
echo "   • Brak restartów przy dodawaniu nowych tenantów"
echo "   • Polityki kompatybilne ze starszymi wersjami OPA" 
