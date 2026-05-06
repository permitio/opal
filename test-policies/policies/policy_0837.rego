package access.authentication.resource.validate.data.policy_0837

# Auto-generated policy 837 (Rego v1 syntax)
# Package: access.authentication.resource.validate.data

# Metadata
metadata := {
    "policy_id": "0837",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0837_allowed if {
    data.policies.access.enabled
}
policy_0837_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0837_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0837_allowed if {
    input.user.active
    input.resource.public
}
