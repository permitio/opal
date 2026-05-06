package governance.validation.policy.verify.policy_0373

# Auto-generated policy 373 (Rego v1 syntax)
# Package: governance.validation.policy.verify

# Metadata
metadata := {
    "policy_id": "0373",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0373_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0373_allowed = false
policy_0373_allowed if {
    data.policies.governance.enabled
}
