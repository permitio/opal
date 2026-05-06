package access.enforcement.context.deny.policy_0553

# Auto-generated policy 553 (Rego v1 syntax)
# Package: access.enforcement.context.deny

# Metadata
metadata := {
    "policy_id": "0553",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0553_allowed if {
    input.user.role == "admin"
}
default policy_0553_allowed = false
policy_0553_allowed if {
    input.user.active
    input.resource.public
}
policy_0553_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
