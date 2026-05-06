package audit.authorization.context.allow.policy_0269

# Auto-generated policy 269 (Rego v1 syntax)
# Package: audit.authorization.context.allow

# Metadata
metadata := {
    "policy_id": "0269",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0269_allowed if {
    input.user.active
    input.resource.public
}
policy_0269_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
