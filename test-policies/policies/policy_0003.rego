package risk.monitoring.action.verify.data.policy_0003

# Auto-generated policy 3 (Rego v1 syntax)
# Package: risk.monitoring.action.verify.data

# Metadata
metadata := {
    "policy_id": "0003",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0003_allowed if {
    input.user.role == "admin"
}
default policy_0003_allowed = false
policy_0003_allowed if {
    data.policies.risk.enabled
}
policy_0003_allowed if {
    input.user.active
    input.resource.public
}
