package audit.authorization.action.verify.policy_0085

# Auto-generated policy 85 (Rego v1 syntax)
# Package: audit.authorization.action.verify

# Metadata
metadata := {
    "policy_id": "0085",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0085_allowed if {
    input.user.active
    input.resource.public
}
policy_0085_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
