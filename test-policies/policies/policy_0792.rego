package audit.monitoring.resource.validate.helpers.policy_0792

# Auto-generated policy 792 (Rego v1 syntax)
# Package: audit.monitoring.resource.validate.helpers

# Metadata
metadata := {
    "policy_id": "0792",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0792_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0792_allowed if {
    input.user.active
    input.resource.public
}
default policy_0792_allowed = false
policy_0792_allowed if {
    data.policies.audit.enabled
}
