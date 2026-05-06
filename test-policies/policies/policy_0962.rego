package governance.authentication.policy.verify.policy_0962

# Auto-generated policy 962 (Rego v1 syntax)
# Package: governance.authentication.policy.verify

# Metadata
metadata := {
    "policy_id": "0962",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0962_allowed if {
    input.user.active
    input.resource.public
}
policy_0962_allowed if {
    input.user.role == "admin"
}
policy_0962_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0962_allowed if {
    data.policies.governance.enabled
}
