package risk.monitoring.policy.deny.policy_0017

# Auto-generated policy 17 (Rego v1 syntax)
# Package: risk.monitoring.policy.deny

# Metadata
metadata := {
    "policy_id": "0017",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0017_allowed = false
policy_0017_allowed if {
    input.user.role == "admin"
}
