package access.monitoring.context.check.policy_0572

# Auto-generated policy 572 (Rego v1 syntax)
# Package: access.monitoring.context.check

# Metadata
metadata := {
    "policy_id": "0572",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0572_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0572_allowed = false
policy_0572_allowed if {
    input.user.active
    input.resource.public
}
policy_0572_allowed if {
    data.policies.access.enabled
}
