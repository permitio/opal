package risk.monitoring.resource.deny.policy_0049

# Auto-generated policy 49 (Rego v1 syntax)
# Package: risk.monitoring.resource.deny

# Metadata
metadata := {
    "policy_id": "0049",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0049_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0049_allowed = false
policy_0049_allowed if {
    data.policies.risk.enabled
}
policy_0049_allowed if {
    input.user.role == "admin"
}
