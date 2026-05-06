package audit.authorization.context.check.policy_0641

# Auto-generated policy 641 (Rego v1 syntax)
# Package: audit.authorization.context.check

# Metadata
metadata := {
    "policy_id": "0641",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0641_allowed if {
    input.user.role == "admin"
}
default policy_0641_allowed = false
policy_0641_allowed if {
    input.user.active
    input.resource.public
}
policy_0641_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
