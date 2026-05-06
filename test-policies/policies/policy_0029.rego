package risk.monitoring.resource.check.core.policy_0029

# Auto-generated policy 29 (Rego v1 syntax)
# Package: risk.monitoring.resource.check.core

# Metadata
metadata := {
    "policy_id": "0029",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0029_allowed if {
    data.policies.risk.enabled
}
policy_0029_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
