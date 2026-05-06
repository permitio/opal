package access.monitoring.user.validate.policy_0814

# Auto-generated policy 814 (Rego v1 syntax)
# Package: access.monitoring.user.validate

# Metadata
metadata := {
    "policy_id": "0814",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0814_allowed if {
    input.user.active
    input.resource.public
}
policy_0814_allowed if {
    input.user.role == "admin"
}
policy_0814_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
