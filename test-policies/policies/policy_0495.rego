package compliance.authorization.action.verify.policy_0495

# Auto-generated policy 495 (Rego v1 syntax)
# Package: compliance.authorization.action.verify

# Metadata
metadata := {
    "policy_id": "0495",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0495_allowed if {
    input.user.role == "admin"
}
default policy_0495_allowed = false
policy_0495_allowed if {
    input.user.active
    input.resource.public
}
policy_0495_allowed if {
    data.policies.compliance.enabled
}
