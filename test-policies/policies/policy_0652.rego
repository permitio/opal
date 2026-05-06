package access.monitoring.resource.check.policy_0652

# Auto-generated policy 652 (Rego v1 syntax)
# Package: access.monitoring.resource.check

# Metadata
metadata := {
    "policy_id": "0652",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0652_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0652_allowed if {
    data.policies.access.enabled
}
