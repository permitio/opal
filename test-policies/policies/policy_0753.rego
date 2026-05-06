package audit.authentication.action.verify.policy_0753

# Auto-generated policy 753 (Rego v1 syntax)
# Package: audit.authentication.action.verify

# Metadata
metadata := {
    "policy_id": "0753",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0753_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0753_allowed if {
    input.user.active
    input.resource.public
}
