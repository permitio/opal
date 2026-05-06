package security.monitoring.context.validate.logic.policy_0231

# Auto-generated policy 231 (Rego v1 syntax)
# Package: security.monitoring.context.validate.logic

# Metadata
metadata := {
    "policy_id": "0231",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0231_allowed if {
    input.user.active
    input.resource.public
}
default policy_0231_allowed = false
policy_0231_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0231_allowed if {
    input.user.role == "admin"
}
