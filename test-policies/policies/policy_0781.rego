package risk.enforcement.resource.validate.policy_0781

# Auto-generated policy 781 (Rego v1 syntax)
# Package: risk.enforcement.resource.validate

# Metadata
metadata := {
    "policy_id": "0781",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0781_allowed if {
    input.user.role == "admin"
}
policy_0781_allowed if {
    input.user.active
    input.resource.public
}
default policy_0781_allowed = false
