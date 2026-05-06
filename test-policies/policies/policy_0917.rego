package risk.validation.resource.deny.policy_0917

# Auto-generated policy 917 (Rego v1 syntax)
# Package: risk.validation.resource.deny

# Metadata
metadata := {
    "policy_id": "0917",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0917_allowed if {
    data.policies.risk.enabled
}
default policy_0917_allowed = false
