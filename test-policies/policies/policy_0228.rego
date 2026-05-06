package risk.validation.resource.deny.policy_0228

# Auto-generated policy 228 (Rego v1 syntax)
# Package: risk.validation.resource.deny

# Metadata
metadata := {
    "policy_id": "0228",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0228_allowed = false
policy_0228_allowed if {
    input.user.active
    input.resource.public
}
