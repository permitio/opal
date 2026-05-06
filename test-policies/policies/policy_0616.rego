package risk.monitoring.user.validate.helpers.policy_0616

# Auto-generated policy 616 (Rego v1 syntax)
# Package: risk.monitoring.user.validate.helpers

# Metadata
metadata := {
    "policy_id": "0616",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0616_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0616_allowed if {
    data.policies.risk.enabled
}
policy_0616_allowed if {
    input.user.role == "admin"
}
policy_0616_allowed if {
    input.user.active
    input.resource.public
}
