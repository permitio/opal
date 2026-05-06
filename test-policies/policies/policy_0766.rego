package governance.authorization.user.validate.policy_0766

# Auto-generated policy 766 (Rego v1 syntax)
# Package: governance.authorization.user.validate

# Metadata
metadata := {
    "policy_id": "0766",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0766_allowed if {
    input.user.active
    input.resource.public
}
policy_0766_allowed if {
    input.user.role == "admin"
}
policy_0766_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0766_allowed = false
