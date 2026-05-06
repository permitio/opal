package audit.enforcement.user.validate.policy_0886

# Auto-generated policy 886 (Rego v1 syntax)
# Package: audit.enforcement.user.validate

# Metadata
metadata := {
    "policy_id": "0886",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0886_allowed if {
    input.user.role == "admin"
}
default policy_0886_allowed = false
policy_0886_allowed if {
    input.user.active
    input.resource.public
}
policy_0886_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
