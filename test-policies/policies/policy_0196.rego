package audit.authentication.user.validate.policy_0196

# Auto-generated policy 196 (Rego v1 syntax)
# Package: audit.authentication.user.validate

# Metadata
metadata := {
    "policy_id": "0196",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0196_allowed if {
    input.user.role == "admin"
}
default policy_0196_allowed = false
policy_0196_allowed if {
    input.user.active
    input.resource.public
}
